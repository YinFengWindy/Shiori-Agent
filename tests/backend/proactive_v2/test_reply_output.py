from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.roles.reply_state import InvalidRoleReply, RoleReplyContext
from proactive_v2.context import AgentTickContext
from proactive_v2.reply_output import correct_push_call, parse_push_reply, reply_schemas
from proactive_v2.tools import TOOL_SCHEMAS


def _context():
    return AgentTickContext(reply_context=RoleReplyContext(("平静", "开心"), "before"))


def _call(**updates):
    return {
        "name": "message_push",
        "input": {
            "message": "晚上好",
            "mood": "开心",
            "thought": "我想陪你聊聊。",
            **updates,
        },
    }


@pytest.mark.parametrize(
    "updates",
    [
        {"mood": "unknown"},
        {"mood": None},
        {"thought": "他想休息"},
        {"thought": "我" * 101},
        {"thought": ""},
        {"message": ""},
    ],
)
def test_rejects_invalid_formal_fields(updates):
    with pytest.raises(InvalidRoleReply):
        parse_push_reply(_call(**updates)["input"], _context())


def test_image_only_still_requires_valid_mood_and_thought():
    ctx = _context()
    reply = parse_push_reply(_call(message="", image="/tmp/cat.png")["input"], ctx)
    assert reply.content == ""
    with pytest.raises(InvalidRoleReply):
        parse_push_reply(_call(message="", media=[" "], mood="开心")["input"], ctx)
    with pytest.raises(InvalidRoleReply):
        parse_push_reply(
            _call(message="", image="/tmp/cat.png", thought="")["input"], ctx
        )


def test_role_schema_has_catalog_and_does_not_mutate_global_schemas():
    bound = reply_schemas(TOOL_SCHEMAS, _context())
    parameters = next(
        s["function"]["parameters"]
        for s in bound
        if s["function"]["name"] == "message_push"
    )
    assert parameters["properties"]["mood"]["enum"] == ["平静", "开心"]
    assert {"message", "mood", "thought"} <= set(parameters["required"])
    original = next(
        s["function"]["parameters"]
        for s in TOOL_SCHEMAS
        if s["function"]["name"] == "message_push"
    )
    assert "enum" not in original["properties"]["mood"]


@pytest.mark.asyncio
async def test_invalid_state_corrects_once_with_only_message_push_and_original_history():
    ctx = _context()
    llm = AsyncMock(return_value=_call())
    history = [{"role": "tool", "tool_call_id": "web", "content": "already retrieved"}]
    corrected = await correct_push_call(
        _call(mood="bad"),
        ctx=ctx,
        messages=history,
        schemas=reply_schemas(TOOL_SCHEMAS, ctx),
        llm_fn=llm,
        remaining_steps=2,
    )
    assert corrected == _call()
    assert ctx.reply_format_corrections == 1
    assert ctx.steps_taken == 1
    assert llm.await_args.args[0][0] == history[0]
    assert [s["function"]["name"] for s in llm.await_args.args[1]] == ["message_push"]
    with pytest.raises(InvalidRoleReply):
        await correct_push_call(
            _call(thought=""),
            ctx=ctx,
            messages=history,
            schemas=TOOL_SCHEMAS,
            llm_fn=llm,
            remaining_steps=20,
        )
    assert llm.await_count == 1


@pytest.mark.parametrize(
    "response",
    [
        None,
        {"name": "shell", "input": {"command": "echo no"}},
        _call(mood="bad"),
        _call(image="/tmp/unrequested.png"),
        _call(message="rewritten"),
    ],
)
@pytest.mark.asyncio
async def test_bad_correction_never_becomes_a_tool_execution(response):
    ctx = _context()
    llm = AsyncMock(return_value=response)
    with pytest.raises(InvalidRoleReply):
        await correct_push_call(
            _call(mood="bad"),
            ctx=ctx,
            messages=[],
            schemas=TOOL_SCHEMAS,
            llm_fn=llm,
            remaining_steps=3,
        )
    assert llm.await_count == 1
    assert ctx.role_reply is None


@pytest.mark.asyncio
async def test_no_budget_no_call_and_cancel_never_retries():
    ctx = _context()
    llm = AsyncMock(side_effect=asyncio.CancelledError)
    with pytest.raises(InvalidRoleReply):
        await correct_push_call(
            _call(mood="bad"),
            ctx=ctx,
            messages=[],
            schemas=TOOL_SCHEMAS,
            llm_fn=llm,
            remaining_steps=0,
        )
    llm.assert_not_awaited()
    with pytest.raises(asyncio.CancelledError):
        await correct_push_call(
            _call(mood="bad"),
            ctx=ctx,
            messages=[],
            schemas=TOOL_SCHEMAS,
            llm_fn=llm,
            remaining_steps=1,
        )
    assert llm.await_count == 1
    assert ctx.role_reply is None
