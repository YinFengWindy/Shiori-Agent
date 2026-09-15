"""Successful role replies commit state with messages; failures keep prior state."""

import asyncio
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.core.runtime_support import TurnRunResult
from agent.lifecycle.phase import Phase
from agent.lifecycle.phases.after_reasoning import (
    AfterReasoningFrame,
    default_after_reasoning_modules,
)
from agent.lifecycle.types import AfterReasoningInput, TurnState
from bus.event_bus import EventBus
from bus.events import InboundMessage
from core.roles.reply_state import InvalidRoleReply
from session.manager import SessionManager


def phase(manager):
    return Phase(
        default_after_reasoning_modules(
            EventBus(), SimpleNamespace(session_manager=manager, presence=None)
        ),
        frame_factory=AfterReasoningFrame,
    )


def turn(session, *, mood="平静", thought="我终于放心了。", raw=None):
    reply = (
        raw
        if raw is not None
        else json.dumps(
            {"content": "你好", "mood": mood, "thought": thought}, ensure_ascii=False
        )
    )
    return AfterReasoningInput(
        state=TurnState(
            msg=InboundMessage(
                channel="desktop", chat_id=session.key, sender="user", content="你好"
            ),
            session_key=session.key,
            dispatch_outbound=False,
            session=session,
        ),
        turn_result=TurnRunResult(
            reply=reply, thinking="mood 平静", context_retry={"formal_role_reply": True}
        ),
    )


def role_session(manager, key="role:yin"):
    session = manager.get_or_create(key)
    session.metadata.update(
        {
            "role_id": key.removeprefix("role:"),
            "role_runtime_config": {
                "mood_catalog": ["平静", "害羞"],
                "default_mood": "害羞",
            },
            "current_mood": "害羞",
            "current_thought": "我在等你。",
            "current_thought_updated_at": "old",
        }
    )
    manager.save(session)
    return session


async def test_two_turns_commit_correct_state_without_consolidation_and_survive_restart(
    tmp_path,
):
    manager = SessionManager(tmp_path)
    session = role_session(manager)
    other = role_session(manager, "role:other")
    for mood, thought in [("平静", "我终于放心了。"), ("害羞", "我还是有点不好意思。")]:
        result = await phase(manager).run(turn(session, mood=mood, thought=thought))
        assert result.outbound.content == "你好"
        assert session.messages[-1]["metadata"]["mood"] == mood
        assert session.messages[-1]["metadata"]["thought"] == thought
        assert session.metadata["current_mood"] == mood
        assert session.metadata["current_thought"] == thought
        assert session.last_consolidated == 0
    session.metadata["relationship_snapshot"] = {
        "role_self_view": "我是不应覆盖当轮想法的旧快照。"
    }
    manager.save(session)
    reloaded = SessionManager(tmp_path).get_or_create(session.key)
    assert reloaded.metadata["current_thought"] == "我还是有点不好意思。"
    assert reloaded.metadata["current_mood"] == "害羞"
    assert other.metadata["current_thought"] == "我在等你。"
    assert len(reloaded.messages) == 4


async def test_thinking_mood_cannot_rescue_plain_formal_response(tmp_path):
    manager = SessionManager(tmp_path)
    session = role_session(manager)
    with pytest.raises(InvalidRoleReply):
        await phase(manager).run(turn(session, raw="哼，总算回我了。"))
    assert session.metadata["current_mood"] == "害羞"
    assert session.metadata["current_thought_updated_at"] == "old"
    assert session.messages == []


@pytest.mark.parametrize("failure", [OSError("disk full"), asyncio.CancelledError()])
async def test_failed_append_rolls_back_turn_fields_but_preserves_independent_snapshot(
    tmp_path, failure
):
    manager = SessionManager(tmp_path)
    session = role_session(manager)

    async def failed_append(*args, **kwargs):
        session.metadata["relationship_snapshot"] = {
            "role_self_view": "我来自独立的更新。"
        }
        raise failure

    manager.append_messages = AsyncMock(side_effect=failed_append)
    with pytest.raises(type(failure)):
        await phase(manager).run(turn(session))
    assert session.metadata["current_mood"] == "害羞"
    assert session.metadata["current_thought"] == "我在等你。"
    assert session.metadata["current_thought_updated_at"] == "old"
    assert (
        session.metadata["relationship_snapshot"]["role_self_view"]
        == "我来自独立的更新。"
    )
    assert session.messages == []


async def test_non_model_notification_does_not_infer_role_state(tmp_path):
    manager = SessionManager(tmp_path)
    session = role_session(manager)
    request = turn(session, raw="后台任务完成。")
    request.turn_result.context_retry.clear()
    result = await phase(manager).run(request)
    assert result.outbound.content == "后台任务完成。"
    assert session.metadata["current_thought"] == "我在等你。"


async def test_projection_failure_rolls_back_database_and_cached_role_state(tmp_path):
    from conversation.service import ConversationService, LegacySessionDescriptor

    manager = SessionManager(tmp_path)
    thread = ConversationService(manager).ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="telegram:1", role_id="yin", channel="telegram", chat_id="1"
        )
    )
    session = role_session(manager)
    request = turn(session)
    request.state.msg.metadata["thread_id"] = thread.id
    manager._store._conn.execute(
        "CREATE TRIGGER fail_reply_projection BEFORE INSERT ON role_state BEGIN SELECT RAISE(ABORT, 'projection failed'); END"
    )
    manager._store._conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="projection failed"):
        await phase(manager).run(request)
    assert session.messages == []


async def test_failed_turn_does_not_remove_concurrent_message_or_newer_state(tmp_path):
    manager = SessionManager(tmp_path)
    session = role_session(manager)

    async def concurrent_append(*args, **kwargs):
        session.add_message("assistant", "另一个成功回合")
        session.metadata.update(
            current_mood="平静",
            current_mood_updated_at="newer",
            current_thought="我属于新回合。",
            current_thought_updated_at="newer",
            last_turn_ts="newer",
        )
        raise OSError("old append failed")

    manager.append_messages = AsyncMock(side_effect=concurrent_append)
    with pytest.raises(OSError):
        await phase(manager).run(turn(session))
    assert [message["content"] for message in session.messages] == ["另一个成功回合"]
    assert session.metadata["current_thought"] == "我属于新回合。"
    assert session.metadata["current_mood_updated_at"] == "newer"
    assert session.metadata["last_turn_ts"] == "newer"


async def test_stale_formal_result_does_not_overwrite_later_committed_state(tmp_path):
    manager = SessionManager(tmp_path)
    session = role_session(manager)
    request = turn(session)
    request.turn_result.context_retry["role_reply_previous_updated_at"] = "older"
    session.metadata.update(
        current_mood_updated_at="newer", current_thought="我属于新回合。"
    )
    with pytest.raises(ValueError, match="过时"):
        await phase(manager).run(request)
    assert session.messages == []
    assert session.metadata["current_thought"] == "我属于新回合。"
    assert session.metadata["current_mood"] == "害羞"
    reloaded = SessionManager(tmp_path).get_or_create(session.key)
    assert reloaded.messages == []
    assert reloaded.metadata["current_thought"] == "我在等你。"
