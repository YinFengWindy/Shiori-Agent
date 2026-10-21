"""get_recent_chat drops proactive pushes and context frames, and keeps passive replies."""

from __future__ import annotations

from core.roles.reply_state import RoleReplyContext

import json
from unittest.mock import AsyncMock

import pytest

from proactive_v2.context import AgentTickContext
from proactive_v2.tools import _get_recent_chat


@pytest.mark.asyncio
async def test_get_recent_chat_keeps_passive_assistant_replies():
    """被动回复（role=assistant, proactive 为假）应该保留，代表用户主动发起的对话上下文。"""
    mixed = [
        {"role": "user", "content": "G2 最近状态怎样"},
        {
            "role": "assistant",
            "content": "G2 最近手感不错，jks 发挥稳定",
        },  # 被动回复，无 proactive 字段
        {"role": "user", "content": "了解"},
        {"role": "assistant", "content": "CS2 比赛结果", "proactive": True},  # 主动推送
    ]
    fake_chat_fn = AsyncMock(return_value=mixed)
    ctx = AgentTickContext(
        reply_context=RoleReplyContext(("平静",), ""),
    )

    raw = await _get_recent_chat(ctx, {}, recent_chat_fn=fake_chat_fn)
    result = json.loads(raw)

    contents = [m["content"] for m in result]
    assert "G2 最近手感不错，jks 发挥稳定" in contents, "被动回复应该被保留"
    assert "CS2 比赛结果" not in contents, "主动推送应该被过滤"


@pytest.mark.asyncio
async def test_get_recent_chat_filters_context_frames():
    mixed = [
        {
            "role": "user",
            "content": '<system-reminder data-system-context-frame="true">内部</system-reminder>',
        },
        {"role": "user", "content": "真实用户消息"},
    ]
    fake_chat_fn = AsyncMock(return_value=mixed)
    ctx = AgentTickContext(
        reply_context=RoleReplyContext(("平静",), ""),
    )

    raw = await _get_recent_chat(ctx, {}, recent_chat_fn=fake_chat_fn)
    result = json.loads(raw)

    assert [m["content"] for m in result] == ["真实用户消息"]


@pytest.mark.asyncio
async def test_get_recent_chat_empty_after_filtering_all_proactive():
    """全部是主动推送时，返回空列表。"""
    all_proactive = [
        {"role": "assistant", "content": "push 1", "proactive": True},
        {"role": "assistant", "content": "push 2", "proactive": True},
    ]
    fake_chat_fn = AsyncMock(return_value=all_proactive)
    ctx = AgentTickContext(
        reply_context=RoleReplyContext(("平静",), ""),
    )

    raw = await _get_recent_chat(ctx, {}, recent_chat_fn=fake_chat_fn)
    result = json.loads(raw)

    assert result == []


@pytest.mark.asyncio
async def test_get_recent_chat_all_user_messages_pass_through():
    """没有 assistant 消息时，全量返回用户消息。"""
    user_only = [
        {"role": "user", "content": "hi"},
        {"role": "user", "content": "ok"},
    ]
    fake_chat_fn = AsyncMock(return_value=user_only)
    ctx = AgentTickContext(
        reply_context=RoleReplyContext(("平静",), ""),
    )

    raw = await _get_recent_chat(ctx, {}, recent_chat_fn=fake_chat_fn)
    result = json.loads(raw)

    assert result == user_only


@pytest.mark.asyncio
async def test_get_recent_chat_adds_beijing_timestamp_for_prompt_context():
    fake_chat_fn = AsyncMock(
        return_value=[
            {
                "role": "user",
                "content": "刚跑完步",
                "timestamp": "2026-07-14T21:28:54+08:00",
            }
        ]
    )
    ctx = AgentTickContext(
        reply_context=RoleReplyContext(("平静",), ""),
    )

    raw = await _get_recent_chat(ctx, {}, recent_chat_fn=fake_chat_fn)
    result = json.loads(raw)

    assert result[0]["timestamp"] == "2026-07-14T21:28:54+08:00"
    assert result[0]["timestamp_local"] == "2026-07-14 21:28:54 +0800"


@pytest.mark.asyncio
async def test_get_recent_chat_mixed_passive_and_proactive():
    """被动回复和主动推送混合时，只过滤主动推送，被动回复完整保留。"""
    mixed = [
        {"role": "user", "content": "最近睡眠怎样"},
        {
            "role": "assistant",
            "content": "昨晚深睡时间偏少，可能跟熬夜有关",
        },  # 被动回复
        {"role": "user", "content": "嗯"},
        {"role": "assistant", "content": "心率偏高预警", "proactive": True},  # 主动推送
        {"role": "user", "content": "看到了"},
    ]
    fake_chat_fn = AsyncMock(return_value=mixed)
    ctx = AgentTickContext(
        reply_context=RoleReplyContext(("平静",), ""),
    )

    raw = await _get_recent_chat(ctx, {}, recent_chat_fn=fake_chat_fn)
    result = json.loads(raw)

    assert len(result) == 4  # 3 user + 1 passive reply
    proactive_msgs = [m for m in result if m.get("proactive")]
    assert not proactive_msgs
