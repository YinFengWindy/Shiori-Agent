"""Explicit group-context edits preserve omitted fields and reject foreign targets."""

from datetime import datetime
import json
from pathlib import Path

import pytest

from agent.tools.registry import ToolRegistry
from bootstrap.toolsets.groups import register_group_tools
from conversation.service import ConversationService, LegacySessionDescriptor
from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
from session.manager import SessionManager

_OLD = datetime.fromisoformat("2020-01-02T03:04:05+08:00")
_CONTEXT = {
    "role_id": "mira",
    "context_scope": "external",
    "sender_is_user": "true",
    "thread_id": "thread:mira:qq:current",
    "channel": "qq",
}


def _runtime(tmp_path: Path):
    manager = SessionManager(tmp_path)
    conversations = ConversationService(manager)
    environment = GroupEnvironment(tmp_path, manager.conversation_store)
    target = conversations.ensure_thread_for_session(
        LegacySessionDescriptor("telegram:g", "mira", "telegram", "g")
    )
    conversations.remember_contact_name(target, "买房群")
    session = manager.get_or_create("role:mira")
    session.add_message(
        "user", "聊天原文", metadata={"thread_id": target.id, "chat_type": "group"}
    )
    manager.save(session)
    environment.apply(
        "mira",
        GroupEnvironmentUpdate(target.id, "买房群", "旧摘要", "旧笔记"),
        updated_at=_OLD,
    )
    tools = ToolRegistry()
    _ = register_group_tools(tools, tmp_path, manager, (), environment)
    return manager, environment, tools, target


@pytest.mark.asyncio
async def test_bound_user_in_a_group_edits_and_reads_another_channels_context(
    tmp_path: Path,
) -> None:
    _, environment, tools, target = _runtime(tmp_path)
    before = json.loads(
        str(
            await tools.execute(
                "lookup_group_context", {"group_thread_id": target.id}, context=_CONTEXT
            )
        )
    )
    at = datetime.now().astimezone()

    result = json.loads(
        str(
            await tools.execute(
                "update_group_context",
                {
                    "group_thread_id": target.id,
                    "group_note": "新笔记",
                    "summary": "新摘要",
                },
                context=_CONTEXT,
            )
        )
    )
    queried = json.loads(
        str(
            await tools.execute(
                "lookup_group_context", {"group_thread_id": target.id}, context=_CONTEXT
            )
        )
    )

    assert before["group_note"] == "旧笔记"
    assert queried == result
    assert result["group_note"] == "新笔记" and result["summary"] == "新摘要"
    assert (
        at
        <= datetime.fromisoformat(result["summary_updated_at"])
        <= datetime.now().astimezone()
    )
    assert "新笔记" in environment.render_group_note("mira", target.id)
    injected = environment.render_recent_activity(
        "mira", now=datetime.now().astimezone()
    )
    assert "新摘要" in injected and "买房群" in injected
    assert "旧摘要" not in injected


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["group_note", "summary"])
async def test_omitted_field_is_preserved_and_empty_text_clears_only_requested_field(
    tmp_path: Path, field: str
) -> None:
    _, environment, tools, target = _runtime(tmp_path)
    result = json.loads(
        str(
            await tools.execute(
                "update_group_context",
                {"group_thread_id": target.id, field: ""},
                context=_CONTEXT,
            )
        )
    )
    assert result[field] == ""
    if field == "group_note":
        assert result["summary"] == "旧摘要"
        assert result["summary_updated_at"] == _OLD.isoformat()
        assert not environment.note_path("mira", target.id).exists()
    else:
        assert result["group_note"] == "旧笔记"
        assert result["summary_updated_at"] != _OLD.isoformat()
        assert (
            environment.render_recent_activity("mira", now=datetime.now().astimezone())
            == ""
        )


@pytest.mark.asyncio
async def test_unchanged_text_preserves_file_and_summary_timestamp(
    tmp_path: Path,
) -> None:
    manager, environment, tools, target = _runtime(tmp_path)
    path = environment.note_path("mira", target.id)
    file_before = path.stat().st_mtime_ns
    state_before = manager.conversation_store.get_thread_state(target.id)
    result = json.loads(
        str(
            await tools.execute(
                "update_group_context",
                {
                    "group_thread_id": target.id,
                    "group_note": " 旧笔记 ",
                    "summary": "旧摘要",
                },
                context=_CONTEXT,
            )
        )
    )
    assert result["summary_updated_at"] == _OLD.isoformat()
    assert path.stat().st_mtime_ns == file_before
    assert manager.conversation_store.get_thread_state(target.id) == state_before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [{}, {"group_note": None}, {"summary": 4}, {"group_note": [], "summary": "合法"}],
)
async def test_invalid_edit_fields_fail_without_writing(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    _, environment, tools, target = _runtime(tmp_path)
    before = environment.read("mira", target.id)
    result = await tools.execute(
        "update_group_context",
        {"group_thread_id": target.id, **changes},
        context=_CONTEXT,
    )
    assert "必须是字符串" in str(result)
    assert environment.read("mira", target.id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("thread_id", [None, "", " ", 3])
async def test_invalid_target_is_not_replaced_by_the_current_thread(
    tmp_path: Path, thread_id: object
) -> None:
    _, environment, tools, target = _runtime(tmp_path)
    before = environment.read("mira", target.id)
    result = await tools.execute(
        "update_group_context",
        {"group_thread_id": thread_id, "summary": "新摘要"},
        context=_CONTEXT,
    )
    assert "必须提供 group_thread_id" in str(result)
    assert environment.read("mira", target.id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["other_role", "archived", "private", "unknown", "desktop", "scheduler"]
)
async def test_disallowed_target_and_role_spoof_cannot_write(
    tmp_path: Path, kind: str
) -> None:
    manager, environment, tools, target = _runtime(tmp_path)
    role_id = "nova" if kind == "other_role" else "mira"
    store = manager.conversation_store
    thread = store.upsert_thread(
        thread_id=f"thread:{role_id}:forbidden:{kind}",
        role_id=role_id,
        contact_id=target.contact_id,
        channel="telegram",
        thread_kind=kind if kind in {"desktop", "scheduler"} else "network",
        external_thread_id=kind,
        legacy_session_key=f"forbidden:{kind}",
        archived=kind == "archived",
    )
    session = manager.get_or_create(f"role:{role_id}")
    session.add_message(
        "user",
        "秘密",
        metadata={
            "thread_id": thread.id,
            "chat_type": kind if kind in {"private", "unknown"} else "group",
        },
    )
    manager.save(session)
    environment.apply(
        role_id,
        GroupEnvironmentUpdate(thread.id, "群", "秘密摘要", "秘密笔记"),
        updated_at=_OLD,
    )
    before = environment.read(role_id, thread.id)

    result = await tools.execute(
        "update_group_context",
        {"role_id": role_id, "group_thread_id": thread.id, "summary": "覆盖"},
        context=_CONTEXT,
    )

    assert "找不到当前角色所属的群会话" in str(result)
    assert environment.read(role_id, thread.id) == before
    missing_context = await tools.execute(
        "update_group_context",
        {"role_id": role_id, "group_thread_id": thread.id, "summary": "覆盖"},
        context={},
    )
    assert "当前回合没有角色" in str(missing_context)
    assert environment.read(role_id, thread.id) == before
